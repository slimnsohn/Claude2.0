const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { parseBookmarks, mergeSites } = require('../src/core/bookmarks.js');

const VALID = fs.readFileSync(path.join(__dirname, 'fixtures', 'bookmarks-valid.json'), 'utf8');
const CORRUPT = fs.readFileSync(path.join(__dirname, 'fixtures', 'bookmarks-corrupt.json'), 'utf8');

test('parses bookmark bar urls as site items', () => {
  const items = parseBookmarks(VALID);
  const espn = items.find((i) => i.title === 'ESPN');
  assert.ok(espn);
  assert.strictEqual(espn.type, 'site');
  assert.strictEqual(espn.target, 'https://www.espn.com/');
});

test('recurses into bookmark bar folders', () => {
  const items = parseBookmarks(VALID);
  const nested = items.find((i) => i.title === 'Mortgage Rates');
  assert.ok(nested, 'nested folder bookmark should be indexed');
});

test('ignores the "other" and "synced" roots', () => {
  const items = parseBookmarks(VALID);
  assert.strictEqual(items.find((i) => i.title === 'Hidden Other'), undefined);
  assert.strictEqual(items.length, 3);
});

test('throws on corrupt JSON', () => {
  assert.throws(() => parseBookmarks(CORRUPT));
});

test('throws on valid JSON with wrong shape', () => {
  assert.throws(() => parseBookmarks('{"not_roots": {}}'));
});

test('mergeSites de-dupes by normalized URL, bookmarks win over builtins', () => {
  const bookmarks = parseBookmarks(VALID); // contains https://claude.ai/
  const builtins = [
    { id: 'b1', type: 'site', title: 'Claude', subtitle: 'built-in', target: 'https://claude.ai' },
    { id: 'b2', type: 'site', title: 'Gmail', subtitle: 'built-in', target: 'https://mail.google.com' },
  ];
  const merged = mergeSites(bookmarks, builtins);
  const claudes = merged.filter((i) => /claude\.ai/.test(i.target));
  assert.strictEqual(claudes.length, 1);
  assert.notStrictEqual(claudes[0].subtitle, 'built-in');
  assert.ok(merged.find((i) => i.title === 'Gmail'), 'non-duplicate builtins kept');
});

'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { pinKey, isPinned, filterItems, move } = require('../src/core/appbrowser.js');

const ITEMS = [
  { type: 'app', title: 'Excel', target: 'C:\\x\\Excel.lnk' },
  { type: 'app', title: 'cursor', target: 'C:\\x\\Cursor.lnk' },
  { type: 'folder', title: 'Downloads', target: 'C:\\Users\\me\\Downloads' },
  { type: 'site', title: 'GitHub', target: 'https://github.com' },
];

test('pinKey is type:target', () => {
  assert.strictEqual(pinKey({ type: 'app', target: 'C:\\x\\Excel.lnk' }), 'app:C:\\x\\Excel.lnk');
});

test('isPinned matches on type+target, not title', () => {
  const pinned = [{ type: 'app', title: 'Excel Renamed', target: 'C:\\x\\Excel.lnk' }];
  assert.strictEqual(isPinned(pinned, ITEMS[0]), true);
  assert.strictEqual(isPinned(pinned, ITEMS[1]), false);
  assert.strictEqual(isPinned([], ITEMS[0]), false);
  assert.strictEqual(isPinned(undefined, ITEMS[0]), false);
});

test('filterItems returns everything sorted alphabetically (case-insensitive) by default', () => {
  const out = filterItems(ITEMS, {});
  assert.deepStrictEqual(out.map((i) => i.title), ['cursor', 'Downloads', 'Excel', 'GitHub']);
});

test('filterItems narrows by type', () => {
  const out = filterItems(ITEMS, { type: 'app' });
  assert.deepStrictEqual(out.map((i) => i.title), ['cursor', 'Excel']);
});

test('filterItems narrows by case-insensitive title substring', () => {
  const out = filterItems(ITEMS, { query: 'cur' });
  assert.deepStrictEqual(out.map((i) => i.title), ['cursor']);
});

test('filterItems combines type and query', () => {
  const out = filterItems(ITEMS, { type: 'app', query: 'c' });
  assert.deepStrictEqual(out.map((i) => i.title), ['cursor', 'Excel']); // both apps contain "c"
});

test('filterItems tolerates empty input', () => {
  assert.deepStrictEqual(filterItems(undefined, {}), []);
  assert.deepStrictEqual(filterItems([], { type: 'app' }), []);
});

test('move returns a new array with the item relocated', () => {
  const a = ['a', 'b', 'c', 'd'];
  assert.deepStrictEqual(move(a, 0, 2), ['b', 'c', 'a', 'd']);
  assert.deepStrictEqual(move(a, 3, 0), ['d', 'a', 'b', 'c']);
  assert.deepStrictEqual(a, ['a', 'b', 'c', 'd'], 'input is not mutated');
});

test('move clamps out-of-range targets and ignores no-ops', () => {
  const a = ['a', 'b', 'c'];
  assert.deepStrictEqual(move(a, 0, -5), ['a', 'b', 'c']);
  assert.deepStrictEqual(move(a, 2, 99), ['a', 'b', 'c']);
  assert.deepStrictEqual(move(a, 1, 1), ['a', 'b', 'c']);
});

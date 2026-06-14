'use strict';

const { test } = require('node:test');
const assert = require('node:assert');
const { record, recent, frequent, keyOf } = require('../src/core/history.js');

const app = (t, target, title) => ({ id: target, type: t, title, subtitle: '', target });

test('keyOf is type:target', () => {
  assert.strictEqual(keyOf({ type: 'folder', target: 'C:\\x' }), 'folder:C:\\x');
});

test('record creates and increments counts immutably', () => {
  const h0 = { version: 1, items: {} };
  const h1 = record(h0, app('app', 'C:\\a.lnk', 'A'), 1000);
  assert.strictEqual(h1.items['app:C:\\a.lnk'].count, 1);
  assert.strictEqual(h1.items['app:C:\\a.lnk'].lastLaunched, 1000);
  const h2 = record(h1, app('app', 'C:\\a.lnk', 'A'), 2000);
  assert.strictEqual(h2.items['app:C:\\a.lnk'].count, 2);
  assert.strictEqual(h2.items['app:C:\\a.lnk'].lastLaunched, 2000);
  assert.strictEqual(h0.items['app:C:\\a.lnk'], undefined); // h0 untouched
});

test('record bootstraps from a null/empty history (cold start)', () => {
  const h = record(null, { id: 'x', type: 'app', title: 'X', subtitle: '', target: 'C:\\x.lnk' }, 1);
  assert.deepStrictEqual(h, {
    version: 1,
    items: { 'app:C:\\x.lnk': { type: 'app', title: 'X', subtitle: '', target: 'C:\\x.lnk', count: 1, lastLaunched: 1 } },
  });
});

test('record ignores non-trackable types and targetless items', () => {
  const h0 = { version: 1, items: {} };
  assert.strictEqual(record(h0, { type: 'claude', target: 'https://claude.ai/new' }, 1), h0);
  assert.strictEqual(record(h0, { type: 'calc', target: '4' }, 1), h0);
  assert.strictEqual(record(h0, { type: 'app', target: '' }, 1), h0);
});

test('recent orders newest-first and respects limit + typeFilter', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  h = record(h, app('site', 'https://s', 'S'), 200);
  h = record(h, app('folder', 'C:\\f', 'F'), 300);
  const all = recent(h, { typeFilter: 'all', limit: 2 });
  assert.deepStrictEqual(all.map((i) => i.title), ['F', 'S']);
  const apps = recent(h, { typeFilter: 'app', limit: 5 });
  assert.deepStrictEqual(apps.map((i) => i.title), ['A']);
});

test('frequent orders by count then lastLaunched, respects limit + filter', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 110); // A: count 2
  h = record(h, app('app', 'C:\\b.lnk', 'B'), 120); // B: count 1, newer
  h = record(h, app('site', 'https://s', 'S'), 130);
  h = record(h, app('site', 'https://s', 'S'), 140); // S: count 2, newest
  const top = frequent(h, { typeFilter: 'all', limit: 2 });
  assert.deepStrictEqual(top.map((i) => i.title), ['S', 'A']); // both count 2, S newer
  const apps = frequent(h, { typeFilter: 'app', limit: 5 });
  assert.deepStrictEqual(apps.map((i) => i.title), ['A', 'B']);
});

test('recent/frequent return launchable items with id', () => {
  let h = record({ version: 1, items: {} }, app('app', 'C:\\a.lnk', 'A'), 100);
  const [it] = recent(h, { typeFilter: 'all', limit: 1 });
  assert.deepStrictEqual(it, { id: 'app:C:\\a.lnk', type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' });
});

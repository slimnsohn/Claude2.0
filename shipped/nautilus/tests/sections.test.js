'use strict';

const { test } = require('node:test');
const assert = require('node:assert');
const { buildHome } = require('../src/core/sections.js');
const { record } = require('../src/core/history.js');

const cfg = (over = {}) => {
  const { pinned, ...sectionOver } = over;
  return {
    version: 1,
    sections: {
      pinned: { enabled: true, typeFilter: 'all', limit: 8 },
      recent: { enabled: true, typeFilter: 'all', limit: 5 },
      frequent: { enabled: true, typeFilter: 'all', limit: 5 },
      ...sectionOver,
    },
    pinned: pinned || [],
  };
};

const app = (t, target, title) => ({ id: `${t}:${target}`, type: t, title, subtitle: '', target });

test('buildHome emits headers then items, only for non-empty enabled sections', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  const config = cfg({ pinned: [] });
  const out = buildHome({ config, history: h, index: [] });
  assert.deepStrictEqual(out.map((r) => r.kind === 'header' ? `#${r.label}` : r.item.title),
    ['#Recent', 'A', '#Frequent', 'A']);
});

test('buildHome resolves pinned against the live index, falls back to stored payload', () => {
  const config = {
    version: 1,
    sections: {
      pinned: { enabled: true, typeFilter: 'all', limit: 8 },
      recent: { enabled: false, typeFilter: 'all', limit: 5 },
      frequent: { enabled: false, typeFilter: 'all', limit: 5 },
    },
    pinned: [
      { type: 'app', title: 'Stale', subtitle: '', target: 'C:\\live.lnk' },  // present in index
      { type: 'app', title: 'Gone', subtitle: '', target: 'C:\\gone.lnk' },   // not in index
    ],
  };
  const index = [{ id: 'app:C:\\live.lnk', type: 'app', title: 'Live', subtitle: 'Programs', target: 'C:\\live.lnk' }];
  const out = buildHome({ config, history: { version: 1, items: {} }, index });
  const items = out.filter((r) => r.kind === 'item').map((r) => r.item);
  assert.strictEqual(items[0].title, 'Live');             // live index wins
  assert.strictEqual(items[1].title, 'Gone');             // fallback to stored
  assert.strictEqual(items[1].id, 'app:C:\\gone.lnk');
});

test('buildHome suppresses pinned items from Recent and Frequent', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100); // pinned below
  h = record(h, app('app', 'C:\\b.lnk', 'B'), 200);
  const config = cfg({ pinned: [{ type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' }] });
  const out = buildHome({ config, history: h, index: [] });
  const recentItems = sectionItems(out, 'Recent');
  assert.deepStrictEqual(recentItems.map((i) => i.title), ['B']); // A excluded
});

test('buildHome fills Recent up to limit after removing pinned', () => {
  let h = { version: 1, items: {} };
  for (let i = 0; i < 6; i++) h = record(h, app('app', `C:\\x${i}.lnk`, `X${i}`), 100 + i);
  // pin the two newest so they would otherwise occupy the top of Recent
  const config = cfg({
    recent: { enabled: true, typeFilter: 'all', limit: 3 },
    frequent: { enabled: false, typeFilter: 'all', limit: 5 },
    pinned: [
      { type: 'app', title: 'X5', subtitle: '', target: 'C:\\x5.lnk' },
      { type: 'app', title: 'X4', subtitle: '', target: 'C:\\x4.lnk' },
    ],
  });
  const recentItems = sectionItems(buildHome({ config, history: h, index: [] }), 'Recent');
  assert.deepStrictEqual(recentItems.map((i) => i.title), ['X3', 'X2', 'X1']); // 3 filled, not 1
});

test('buildHome omits a disabled section entirely', () => {
  let h = record({ version: 1, items: {} }, app('app', 'C:\\a.lnk', 'A'), 100);
  const config = cfg({ recent: { enabled: false, typeFilter: 'all', limit: 5 }, pinned: [] });
  const out = buildHome({ config, history: h, index: [] });
  assert.strictEqual(out.find((r) => r.kind === 'header' && r.label === 'Recent'), undefined);
});

test('buildHome on empty everything returns []', () => {
  const config = cfg({ pinned: [] });
  assert.deepStrictEqual(buildHome({ config, history: { version: 1, items: {} }, index: [] }), []);
});

test('buildHome pinned typeFilter excludes non-matching types', () => {
  const config = cfg({
    pinned: [
      { type: 'site', title: 'GH', subtitle: '', target: 'https://github.com' },
      { type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' },
    ],
  });
  config.sections.pinned.typeFilter = 'app';
  const pinned = sectionItems(buildHome({ config, history: { version: 1, items: {} }, index: [] }), 'Pinned');
  assert.deepStrictEqual(pinned.map((i) => i.title), ['A']);
});

test('buildHome with Pinned disabled does not suppress its items from Recent', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  const config = cfg({ pinned: [{ type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' }] });
  config.sections.pinned.enabled = false;
  const out = buildHome({ config, history: h, index: [] });
  assert.strictEqual(out.find((r) => r.kind === 'header' && r.label === 'Pinned'), undefined);
  assert.deepStrictEqual(sectionItems(out, 'Recent').map((i) => i.title), ['A']);
});

test('buildHome dedups pinned sites/folders against live index using type:target keys', () => {
  let h = { version: 1, items: {} };
  // history items get type:target keys via keyOf
  h = record(h, { id: 'x', type: 'site', title: 'GH', subtitle: '', target: 'https://gh' }, 100);
  h = record(h, { id: 'y', type: 'folder', title: 'F', subtitle: '', target: 'C:\\f' }, 200);
  // live index uses the REAL scanner id schemes, NOT type:target
  const index = [
    { id: 'bm:https://gh', type: 'site', title: 'GitHub', subtitle: 'gh', target: 'https://gh' },
    { id: 'dir:C:\\f', type: 'folder', title: 'Folder F', subtitle: '', target: 'C:\\f' },
  ];
  const config = cfg({
    frequent: { enabled: false, typeFilter: 'all', limit: 5 },
    pinned: [
      { type: 'site', title: 'GH', subtitle: '', target: 'https://gh' },
      { type: 'folder', title: 'F', subtitle: '', target: 'C:\\f' },
    ],
  });
  const out = buildHome({ config, history: h, index });
  // pinned resolved from the live index (fresh titles), normalized ids
  assert.deepStrictEqual(sectionItems(out, 'Pinned').map((i) => i.title), ['GitHub', 'Folder F']);
  assert.deepStrictEqual(sectionItems(out, 'Pinned').map((i) => i.id), ['site:https://gh', 'folder:C:\\f']);
  // and therefore suppressed from Recent
  assert.deepStrictEqual(sectionItems(out, 'Recent'), []);
});

function sectionItems(rows, label) {
  const start = rows.findIndex((r) => r.kind === 'header' && r.label === label);
  if (start === -1) return [];
  const items = [];
  for (let i = start + 1; i < rows.length && rows[i].kind === 'item'; i++) items.push(rows[i].item);
  return items;
}

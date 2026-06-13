const { test } = require('node:test');
const assert = require('node:assert');
const { score, rankItems } = require('../src/core/score.js');

function item(overrides) {
  return { id: 'x', type: 'app', title: 'X', subtitle: '', target: 'x', ...overrides };
}

test('exact-prefix match scores in the 1000 tier', () => {
  const s = score('vis', 'Visual Studio Code');
  assert.ok(s >= 1000 && s < 1100, `expected [1000,1100), got ${s}`);
});

test('exact full-title match scores in the top tier', () => {
  const s = score('chrome', 'Chrome');
  assert.ok(s >= 1300, `expected >=1300, got ${s}`);
});

test('exact word match outranks title-prefix ("chrome" finds Google Chrome over Chrome Remote Desktop)', () => {
  assert.ok(score('chrome', 'Google Chrome') > score('chrome', 'Chrome Remote Desktop'));
});

test('matching is case-insensitive', () => {
  assert.strictEqual(score('CHRO', 'Google Chrome') > 0, true);
  assert.strictEqual(score('chro', 'GOOGLE CHROME') > 0, true);
});

test('word-boundary prefix scores in the 800 tier (below exact-prefix)', () => {
  const s = score('cod', 'Visual Studio Code');
  assert.ok(s >= 800 && s < 1000, `expected [800,1000), got ${s}`);
});

test('substring match scores in the 600 tier', () => {
  const s = score('sual', 'Visual Studio Code');
  assert.ok(s >= 600 && s < 800, `expected [600,800), got ${s}`);
});

test('acronym match scores in the 450 tier', () => {
  const s = score('vsc', 'Visual Studio Code');
  assert.ok(s >= 450 && s < 600, `expected [450,600), got ${s}`);
});

test('subsequence match scores in the 300 tier', () => {
  const s = score('vstc', 'Visual Studio Code'); // not acronym, not substring
  assert.ok(s >= 300 && s < 450, `expected [300,450), got ${s}`);
});

test('no match scores 0', () => {
  assert.strictEqual(score('zzz', 'Visual Studio Code'), 0);
});

test('empty or whitespace query scores 0', () => {
  assert.strictEqual(score('', 'Chrome'), 0);
  assert.strictEqual(score('   ', 'Chrome'), 0);
});

test('shorter title wins between same-tier matches', () => {
  assert.ok(score('chrome', 'Chrome') > score('chrome', 'Chrome Remote Desktop Host Helper'));
});

test('rankItems sorts descending and drops non-matches', () => {
  const items = [
    item({ id: 'a', title: 'Notepad' }),
    item({ id: 'b', title: 'Google Chrome' }),
    item({ id: 'c', title: 'Chrome Remote Desktop' }),
  ];
  const ranked = rankItems('chrome', items);
  assert.deepStrictEqual(ranked.map((r) => r.id), ['b', 'c']);
  assert.ok(ranked[0].score > ranked[1].score);
});

test('rankItems breaks title ties by type priority app > site > folder', () => {
  const items = [
    item({ id: 'f', type: 'folder', title: 'Downloads' }),
    item({ id: 'a', type: 'app', title: 'Downloads' }),
    item({ id: 's', type: 'site', title: 'Downloads' }),
  ];
  const ranked = rankItems('down', items);
  assert.deepStrictEqual(ranked.map((r) => r.id), ['a', 's', 'f']);
});

test('rankItems returns empty array for empty query', () => {
  assert.deepStrictEqual(rankItems('', [item({ title: 'Chrome' })]), []);
});

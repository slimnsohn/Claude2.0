const { test } = require('node:test');
const assert = require('node:assert');
const { stripVerbs, isQuestionShaped, askClaudeItem, route } = require('../src/core/router.js');

const ITEMS = [
  { id: 'chrome', type: 'app', title: 'Google Chrome', subtitle: '', target: 'chrome.lnk' },
  { id: 'cursor', type: 'app', title: 'Cursor', subtitle: '', target: 'cursor.lnk' },
  { id: 'gmail', type: 'site', title: 'Gmail', subtitle: 'mail.google.com', target: 'https://mail.google.com' },
  { id: 'dl', type: 'folder', title: 'Downloads', subtitle: '', target: 'C:\\Users\\x\\Downloads' },
];

test('stripVerbs removes leading launch verbs only', () => {
  assert.strictEqual(stripVerbs('open chrome'), 'chrome');
  assert.strictEqual(stripVerbs('go to gmail'), 'gmail');
  assert.strictEqual(stripVerbs('launch excel'), 'excel');
  assert.strictEqual(stripVerbs('OPEN Chrome'), 'Chrome');
  assert.strictEqual(stripVerbs('reopen tabs'), 'reopen tabs');
  assert.strictEqual(stripVerbs('chrome open'), 'chrome open');
});

test('isQuestionShaped true for question-word starts', () => {
  assert.strictEqual(isQuestionShaped('help me set up python', true), true);
  assert.strictEqual(isQuestionShaped('where can I find my taxes', true), true);
  assert.strictEqual(isQuestionShaped('what should I eat', false), true);
  assert.strictEqual(isQuestionShaped('how do I do this', false), true);
});

test('isQuestionShaped true for multi-word text without a strong match', () => {
  assert.strictEqual(isQuestionShaped('best pizza near me', false), true);
});

test('isQuestionShaped false for short keyword queries', () => {
  assert.strictEqual(isQuestionShaped('chrome', false), false);
  assert.strictEqual(isQuestionShaped('google chrome', false), false);
});

test('isQuestionShaped false for multi-word query WITH a strong match', () => {
  assert.strictEqual(isQuestionShaped('chrome remote desktop', true), false);
});

test('askClaudeItem URL-encodes the raw query', () => {
  const it = askClaudeItem('how do I set up python?');
  assert.strictEqual(it.type, 'claude');
  assert.strictEqual(it.target, 'https://claude.ai/new?q=how%20do%20I%20set%20up%20python%3F');
});

test('route: strong match first, Ask Claude row last, enterAction is the match', () => {
  const { results, enterAction } = route('chrome', ITEMS);
  assert.strictEqual(results[0].id, 'chrome');
  assert.strictEqual(results[results.length - 1].type, 'claude');
  assert.strictEqual(enterAction.id, 'chrome');
});

test('route: verb is stripped for matching but Claude row keeps raw query', () => {
  const { results, enterAction } = route('open chrome', ITEMS);
  assert.strictEqual(enterAction.id, 'chrome');
  const claudeRow = results.find((r) => r.type === 'claude');
  assert.ok(claudeRow.target.includes(encodeURIComponent('open chrome')));
});

test('route: question-shaped query puts Ask Claude first as enterAction', () => {
  const { results, enterAction } = route('how do I set up python', ITEMS);
  assert.strictEqual(results[0].type, 'claude');
  assert.strictEqual(enterAction.type, 'claude');
});

test('route: multi-word free text with no strong match goes to Claude', () => {
  const { enterAction } = route('best pizza near me tonight', ITEMS);
  assert.strictEqual(enterAction.type, 'claude');
});

test('route: garbage single word with no match still offers Claude', () => {
  const { results, enterAction } = route('zzzqqq', ITEMS);
  assert.strictEqual(results.length, 1);
  assert.strictEqual(results[0].type, 'claude');
  assert.strictEqual(enterAction.type, 'claude');
});

test('route: Ask Claude row appears exactly once', () => {
  for (const q of ['chrome', 'how do I cook rice', 'zz']) {
    const { results } = route(q, ITEMS);
    assert.strictEqual(results.filter((r) => r.type === 'claude').length, 1, `query: ${q}`);
  }
});

test('route: empty query returns no results and null enterAction', () => {
  const { results, enterAction } = route('   ', ITEMS);
  assert.deepStrictEqual(results, []);
  assert.strictEqual(enterAction, null);
});

test('route: folder and site matches launch like apps', () => {
  assert.strictEqual(route('downloads', ITEMS).enterAction.id, 'dl');
  assert.strictEqual(route('gmail', ITEMS).enterAction.id, 'gmail');
});

// ---- prefix overrides: first word ending in a colon forces a type ----

test('folder: prefix restricts results to folders and skips question logic', () => {
  const { results, enterAction } = route('folder: down', ITEMS);
  assert.strictEqual(enterAction.id, 'dl');
  assert.ok(results.filter((r) => r.type !== 'claude').every((r) => r.type === 'folder'));
});

test('site: and website: prefixes restrict to sites', () => {
  assert.strictEqual(route('site:gma', ITEMS).enterAction.id, 'gmail');
  assert.strictEqual(route('website: gmail', ITEMS).enterAction.id, 'gmail');
});

test('app: prefix restricts to apps', () => {
  const { results, enterAction } = route('app:c', ITEMS);
  assert.ok(['chrome', 'cursor'].includes(enterAction.id));
  assert.ok(results.filter((r) => r.type !== 'claude').every((r) => r.type === 'app'));
});

test('claude: prefix forces Ask Claude even for app-looking queries', () => {
  const { results, enterAction } = route('claude: open chrome', ITEMS);
  assert.strictEqual(results.length, 1);
  assert.strictEqual(enterAction.type, 'claude');
  assert.ok(enterAction.target.includes(encodeURIComponent('open chrome')));
});

test('type prefix with empty remainder lists all items of that type', () => {
  const { results, enterAction } = route('folder:', ITEMS);
  assert.strictEqual(enterAction.type, 'folder');
  assert.ok(results.filter((r) => r.type !== 'claude').every((r) => r.type === 'folder'));
});

test('prefix only counts as the first word — colon later in query is plain text', () => {
  const { enterAction } = route('my folder: stuff', ITEMS);
  assert.strictEqual(enterAction.type, 'claude'); // 3 words, no strong match
});

// ---- calculator ----

test('route: =expression puts the calc result first as enterAction', () => {
  const { results, enterAction } = route('=2+2', ITEMS);
  assert.strictEqual(results[0].type, 'calc');
  assert.strictEqual(results[0].title, '= 4');
  assert.strictEqual(enterAction.type, 'calc');
  assert.strictEqual(results[results.length - 1].type, 'claude');
});

test('route: bare math is auto-detected and calc row comes first', () => {
  const { results, enterAction } = route('15*8.5', ITEMS);
  assert.strictEqual(results[0].type, 'calc');
  assert.strictEqual(results[0].title, '= 127.5');
  assert.strictEqual(enterAction.type, 'calc');
});

test('route: incomplete =expression still shows a placeholder calc row', () => {
  const { results } = route('=2+', ITEMS);
  assert.strictEqual(results[0].type, 'calc');
  assert.strictEqual(results[0].target, '');
});

test('route: plain queries get no calc row', () => {
  const { results } = route('chrome', ITEMS);
  assert.strictEqual(results.find((r) => r.type === 'calc'), undefined);
});

test('route caps ranked results (Claude row still present)', () => {
  const many = Array.from({ length: 30 }, (_, i) => ({
    id: `s${i}`, type: 'site', title: `Chrome Site ${i}`, subtitle: '', target: `https://x${i}.com`,
  }));
  const { results } = route('chrome', many);
  assert.ok(results.length <= 13, `expected <=13, got ${results.length}`);
  assert.strictEqual(results.filter((r) => r.type === 'claude').length, 1);
});

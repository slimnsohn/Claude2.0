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

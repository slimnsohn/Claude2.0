const { test } = require('node:test');
const assert = require('node:assert');
const { launchItem } = require('../src/launch.js');

function item(type, target) {
  return { id: 'x', type, title: 'X', subtitle: '', target };
}

test('app launches via shell.openPath on the .lnk', async () => {
  const calls = [];
  const shell = { openPath: async (p) => { calls.push(p); return ''; }, openExternal: async () => {} };
  const result = await launchItem(item('app', 'C:\\sm\\Chrome.lnk'), { shell });
  assert.deepStrictEqual(calls, ['C:\\sm\\Chrome.lnk']);
  assert.deepStrictEqual(result, { ok: true });
});

test('folder launches via shell.openPath', async () => {
  const calls = [];
  const shell = { openPath: async (p) => { calls.push(p); return ''; }, openExternal: async () => {} };
  const result = await launchItem(item('folder', 'C:\\Users\\x\\Downloads'), { shell });
  assert.deepStrictEqual(calls, ['C:\\Users\\x\\Downloads']);
  assert.strictEqual(result.ok, true);
});

test('openPath error string returns ok:false with the error', async () => {
  const shell = { openPath: async () => 'No application found', openExternal: async () => {} };
  const result = await launchItem(item('app', 'bad.lnk'), { shell });
  assert.deepStrictEqual(result, { ok: false, error: 'No application found' });
});

test('site and claude launch via shell.openExternal', async () => {
  const calls = [];
  const shell = { openPath: async () => '', openExternal: async (u) => { calls.push(u); } };
  await launchItem(item('site', 'https://mail.google.com'), { shell });
  await launchItem(item('claude', 'https://claude.ai/new?q=hi'), { shell });
  assert.deepStrictEqual(calls, ['https://mail.google.com', 'https://claude.ai/new?q=hi']);
});

test('openExternal rejection returns ok:false', async () => {
  const shell = { openPath: async () => '', openExternal: async () => { throw new Error('no browser'); } };
  const result = await launchItem(item('site', 'https://x.com'), { shell });
  assert.strictEqual(result.ok, false);
  assert.match(result.error, /no browser/);
});

test('unknown item type returns ok:false', async () => {
  const shell = { openPath: async () => '', openExternal: async () => {} };
  const result = await launchItem(item('mystery', 'x'), { shell });
  assert.strictEqual(result.ok, false);
});

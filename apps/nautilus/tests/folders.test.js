const { test } = require('node:test');
const assert = require('node:assert');
const { scanFolders } = require('../src/core/folders.js');
const { makeFakeFs } = require('./fixtures/fake-fs.js');

const DESKTOP = 'C:\\Users\\x\\Desktop';
const DOWNLOADS = 'C:\\Users\\x\\Downloads';

const fakeFs = makeFakeFs({
  [DESKTOP]: {
    'Claude 2.0': {
      'apps': {
        'nautilus': { 'src': {} },
      },
      'notes.txt': null,
    },
    'file.txt': null,
    '.hidden': {},
    'node_modules': {},
  },
  [DOWNLOADS]: {},
});

test('includes the roots themselves as items', () => {
  const items = scanFolders([DESKTOP, DOWNLOADS], { listDirSync: fakeFs });
  assert.ok(items.find((i) => i.title === 'Desktop' && i.target === DESKTOP));
  assert.ok(items.find((i) => i.title === 'Downloads' && i.target === DOWNLOADS));
});

test('scans subdirectories up to maxDepth and marks them type folder', () => {
  const items = scanFolders([DESKTOP], { listDirSync: fakeFs, maxDepth: 2 });
  assert.ok(items.find((i) => i.title === 'Claude 2.0'), 'depth 1');
  assert.ok(items.find((i) => i.title === 'apps'), 'depth 2');
  assert.strictEqual(items.find((i) => i.title === 'nautilus'), undefined, 'depth 3 excluded');
  assert.ok(items.every((i) => i.type === 'folder'));
});

test('files are not indexed', () => {
  const items = scanFolders([DESKTOP], { listDirSync: fakeFs });
  assert.strictEqual(items.find((i) => i.title === 'file.txt'), undefined);
  assert.strictEqual(items.find((i) => i.title === 'notes.txt'), undefined);
});

test('hidden and noise folders are skipped', () => {
  const items = scanFolders([DESKTOP], { listDirSync: fakeFs });
  assert.strictEqual(items.find((i) => i.title === '.hidden'), undefined);
  assert.strictEqual(items.find((i) => i.title === 'node_modules'), undefined);
});

test('missing root is skipped without throwing', () => {
  const items = scanFolders(['C:\\nope', DOWNLOADS], { listDirSync: fakeFs });
  assert.ok(items.find((i) => i.title === 'Downloads'));
});

const { test } = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { scanStartMenu } = require('../src/core/startmenu.js');
const { makeFakeFs } = require('./fixtures/fake-fs.js');

const USER_SM = 'C:\\Users\\x\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs';
const SYS_SM = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs';

const fakeFs = makeFakeFs({
  [USER_SM]: {
    'Cursor.lnk': null,
    'readme.txt': null,
    'Dev Tools': {
      'Visual Studio Code.lnk': null,
    },
  },
  [SYS_SM]: {
    'Google Chrome.lnk': null,
    'Cursor.lnk': null,
  },
});

test('finds .lnk files recursively and strips the extension from titles', () => {
  const items = scanStartMenu([USER_SM, SYS_SM], { listDirSync: fakeFs });
  const titles = items.map((i) => i.title).sort();
  assert.deepStrictEqual(titles, ['Cursor', 'Google Chrome', 'Visual Studio Code']);
  assert.ok(items.every((i) => i.type === 'app'));
});

test('target is the full .lnk path', () => {
  const items = scanStartMenu([USER_SM, SYS_SM], { listDirSync: fakeFs });
  const vsc = items.find((i) => i.title === 'Visual Studio Code');
  assert.strictEqual(vsc.target, path.join(USER_SM, 'Dev Tools', 'Visual Studio Code.lnk'));
});

test('subtitle is the folder path relative to the start menu root', () => {
  const items = scanStartMenu([USER_SM, SYS_SM], { listDirSync: fakeFs });
  assert.strictEqual(items.find((i) => i.title === 'Visual Studio Code').subtitle, 'Dev Tools');
  assert.strictEqual(items.find((i) => i.title === 'Google Chrome').subtitle, '');
});

test('duplicate titles across roots are de-duped (first root wins)', () => {
  const items = scanStartMenu([USER_SM, SYS_SM], { listDirSync: fakeFs });
  const cursors = items.filter((i) => i.title === 'Cursor');
  assert.strictEqual(cursors.length, 1);
  assert.strictEqual(cursors[0].target, path.join(USER_SM, 'Cursor.lnk'));
});

test('non-.lnk files are ignored', () => {
  const items = scanStartMenu([USER_SM], { listDirSync: fakeFs });
  assert.strictEqual(items.find((i) => /readme/i.test(i.title)), undefined);
});

test('missing root is skipped without throwing', () => {
  const items = scanStartMenu(['C:\\does\\not\\exist', USER_SM], { listDirSync: fakeFs });
  assert.ok(items.length > 0);
});

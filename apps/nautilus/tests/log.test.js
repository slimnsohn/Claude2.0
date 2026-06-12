const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createLogger } = require('../src/log.js');

test('writes timestamped lines and creates the directory', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nautilus-log-'));
  const logPath = path.join(dir, 'sub', 'launcher.log');
  const log = createLogger(logPath);
  log.info('hello');
  log.error('bad thing');
  const content = fs.readFileSync(logPath, 'utf8');
  assert.match(content, /\d{4}-\d{2}-\d{2}T.*INFO hello/);
  assert.match(content, /ERROR bad thing/);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('never throws even when the path is unwritable', () => {
  const log = createLogger('Z:\\definitely\\not\\a\\real\\drive\\launcher.log');
  assert.doesNotThrow(() => log.info('x'));
  assert.doesNotThrow(() => log.error('y'));
});

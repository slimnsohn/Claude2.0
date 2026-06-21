'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const { iconSlug, iconFor, ICON_DIR } = require('../src/core/iconmap.js');

test('maps a plain app title to its slug', () => {
  assert.strictEqual(iconSlug('Cursor'), 'cursor');
  assert.strictEqual(iconSlug('Excel'), 'excel');
});

test('matches on a token, ignoring vendor words and trailing versions', () => {
  assert.strictEqual(iconSlug('Google Chrome'), 'chrome');
  assert.strictEqual(iconSlug('Microsoft Edge'), 'edge');
  assert.strictEqual(iconSlug('PyCharm 2025.2.3'), 'pycharm');
  assert.strictEqual(iconSlug('VLC media player'), 'vlc');
});

test('matches despite parenthetical suffixes and punctuation', () => {
  assert.strictEqual(iconSlug('Outlook (classic)'), 'outlook');
  assert.strictEqual(iconSlug('Node.js'), 'node');
  assert.strictEqual(iconSlug('Git Bash'), 'git');
  assert.strictEqual(iconSlug('Jupyter Notebook'), 'jupyter');
  assert.strictEqual(iconSlug('Anaconda Navigator'), 'anaconda');
});

test('is case-insensitive', () => {
  assert.strictEqual(iconSlug('EXCEL'), 'excel');
  assert.strictEqual(iconSlug('cursor'), 'cursor');
});

test('returns null for an unknown app', () => {
  assert.strictEqual(iconSlug('Speccy'), null);
  assert.strictEqual(iconSlug('Some Random Tool'), null);
  assert.strictEqual(iconSlug(''), null);
  assert.strictEqual(iconSlug(undefined), null);
});

test('does not false-match on substrings inside a larger word', () => {
  // "word" must not match "WordPad"? (we accept token match only) — "Crossword" should not map to Word
  assert.strictEqual(iconSlug('Crossword Puzzle'), null);
});

test('iconFor: app items resolve to "<slug>.svg"', () => {
  assert.strictEqual(iconFor({ type: 'app', title: 'Excel' }), 'excel.svg');
  assert.strictEqual(iconFor({ type: 'app', title: 'Cursor' }), 'cursor.svg');
});

test('iconFor: unknown app yields null (renderer falls back to badge)', () => {
  assert.strictEqual(iconFor({ type: 'app', title: 'Speccy' }), null);
});

test('iconFor: folders use the generic folder icon', () => {
  assert.strictEqual(iconFor({ type: 'folder', title: 'Downloads' }), 'folder.svg');
});

test('iconFor: sites get no bundled icon (favicon handled in renderer)', () => {
  assert.strictEqual(iconFor({ type: 'site', title: 'GitHub', target: 'https://github.com' }), null);
});

test('every mapped slug has a real SVG asset on disk', () => {
  const titles = ['Cursor', 'Excel', 'Word', 'PowerPoint', 'Outlook (classic)', 'OneNote',
    'Publisher', 'Access', 'Google Chrome', 'Microsoft Edge', 'Discord', 'VLC media player',
    'Claude 2', 'Dropbox', 'TeamViewer', 'PyCharm 2025.2.3', 'Anaconda Navigator',
    'Jupyter Notebook', 'Node.js', 'Git Bash'];
  const slugs = new Set(titles.map(iconSlug));
  slugs.add('folder');
  for (const slug of slugs) {
    assert.ok(slug, 'title should have mapped to a slug');
    const file = path.join(ICON_DIR, `${slug}.svg`);
    assert.ok(fs.existsSync(file), `missing asset: ${slug}.svg`);
    const svg = fs.readFileSync(file, 'utf8').trim();
    assert.ok(svg.startsWith('<svg') && svg.endsWith('</svg>'), `not a clean svg: ${slug}.svg`);
  }
});
